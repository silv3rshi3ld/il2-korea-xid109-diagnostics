from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "workflow_status", ROOT / "tools/workflow-status.py"
)
assert SPEC and SPEC.loader
workflow_status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow_status)


class WorkflowStatusTests(unittest.TestCase):
    def make_run(
        self,
        root: pathlib.Path,
        name: str,
        case: str,
        *,
        duration: int = 60,
        xid109: bool = False,
        complete: bool = True,
    ) -> pathlib.Path:
        run = root / name
        run.mkdir()
        (run / "metadata.json").write_text(
            json.dumps(
                {
                    "case": case,
                    "duration_seconds": duration,
                    "observation_start_utc": "2026-08-15T12:00:10Z",
                    "observation_duration_seconds": duration,
                    "proton_exit_code": 0,
                    "capture_complete": complete,
                    "kernel_capture_complete": True,
                    "capture_warnings": [],
                    "capture_interrupted": False,
                }
            )
        )
        kernel_text = (
            (ROOT / "tests/fixtures/kernel-xid109.log").read_text()
            if xid109
            else "synthetic kernel log without an Xid\n"
        )
        (run / "xid-events.json").write_text(
            json.dumps({"events": workflow_status.parse_kernel_log(kernel_text)})
        )
        (run / "kernel-full.log").write_text(kernel_text)
        (run / "vkd3d.log").write_text(
            "Device lost observed, analyzing breadcrumbs ...\n"
            "Reporting NVIDIA checkpoints for direct queue 0.\n"
            "Found pending command list context 1 in executable state, "
            "TOP_OF_PIPE marker 2, BOTTOM_OF_PIPE marker 1.\n"
            "===== Potential crash region BEGIN =====\n"
            "Command: dispatch\n"
            "===== Potential crash region END =====\n"
            "Done analyzing breadcrumbs ...\n"
            if xid109
            else "synthetic VKD3D log without a device loss\n"
        )
        (run / "proton.log").write_text("synthetic Proton log\n")
        (run / (".capture-complete" if complete else ".capture-in-progress")).touch()
        (run / ".observation-start-recorded").touch()
        return run

    def test_failure_baseline_advances_to_single_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                xid109=True,
            )
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertEqual(workflow_status.next_action(runs, order), "single-queue")

    def test_failure_before_ready_requires_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                xid109=True,
            )
            (run / ".observation-start-recorded").unlink()
            metadata = json.loads((run / "metadata.json").read_text())
            metadata["observation_start_utc"] = None
            metadata["observation_duration_seconds"] = None
            (run / "metadata.json").write_text(json.dumps(metadata))
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertFalse(runs[0]["usable_failure"])
            self.assertIn("READY was not recorded", runs[0]["state"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_stable_baseline_stops_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                duration=600,
            )
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertEqual(workflow_status.next_action(runs, order), "STOP_BASELINE_NO_XID")

    def test_missing_ready_observation_is_not_a_stable_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                duration=600,
            )
            metadata = json.loads((run / "metadata.json").read_text())
            metadata.pop("observation_duration_seconds")
            (run / "metadata.json").write_text(json.dumps(metadata))
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertFalse(runs[0]["stable_valid"])
            self.assertEqual(workflow_status.next_action(runs, order), "baseline")

    def test_incomplete_capture_requires_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                complete=False,
            )
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertEqual(workflow_status.next_action(runs, order), "RECOVER")

    def test_symlinked_run_requires_review_without_being_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "results"
            outside = pathlib.Path(temporary) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "2026-08-15T120000Z-baseline").symlink_to(
                outside, target_is_directory=True
            )
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertEqual(len(runs), 1)
            self.assertTrue(runs[0]["broken"])
            self.assertIn("unsafe symlink", runs[0]["state"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_interrupted_xid_requires_coordinator_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                xid109=True,
            )
            metadata = json.loads((run / "metadata.json").read_text())
            metadata["capture_interrupted"] = True
            (run / "metadata.json").write_text(json.dumps(metadata))
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertTrue(runs[0]["review_required"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_unattributed_xid_cannot_stop_the_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                duration=600,
            )
            kernel = (
                "2026-08-15T14:32:10+0000 kernel: NVRM: Xid "
                "(PCI:0000:01:00): 109, name=unknown, channel 0x00000028, "
                "errorString CTX SWITCH TIMEOUT, Info 0x1c022\n"
            )
            (run / "kernel-full.log").write_text(kernel)
            (run / "xid-events.json").write_text(
                json.dumps({"events": workflow_status.parse_kernel_log(kernel)})
            )
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertFalse(runs[0]["stable_valid"])
            self.assertTrue(runs[0]["review_required"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_device_loss_without_xid_requires_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                duration=600,
            )
            (run / "proton.log").write_text("err: VK_ERROR_DEVICE_LOST\n")
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertFalse(runs[0]["stable_valid"])
            self.assertTrue(runs[0]["review_required"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_different_nvidia_xid_requires_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                duration=600,
            )
            kernel = (
                "2026-08-15T14:32:10+0000 kernel: NVRM: Xid "
                "(PCI:0000:01:00): 31, name=IL2Series.exe, channel 0x00000028\n"
            )
            (run / "kernel-full.log").write_text(kernel)
            (run / "xid-events.json").write_text(
                json.dumps({"events": workflow_status.parse_kernel_log(kernel)})
            )
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertFalse(runs[0]["stable_valid"])
            self.assertTrue(runs[0]["other_xid"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_latest_review_run_overrides_an_older_valid_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                xid109=True,
            )
            latest = self.make_run(
                root,
                "2026-08-15T120100Z-baseline",
                "baseline",
                xid109=True,
            )
            metadata = json.loads((latest / "metadata.json").read_text())
            metadata["capture_warnings"] = ["synthetic warning"]
            (latest / "metadata.json").write_text(json.dumps(metadata))
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_missing_capture_marker_requires_review_not_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                complete=True,
            )
            (run / ".capture-complete").unlink()
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertTrue(runs[0]["broken"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_malformed_complete_metadata_requires_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
            )
            (run / "metadata.json").write_text("{not-json\n")
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertTrue(runs[0]["broken"])
            self.assertIn("metadata is malformed", runs[0]["state"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_invalid_failure_duration_is_displayed_as_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                xid109=True,
            )
            metadata = json.loads((run / "metadata.json").read_text())
            metadata["duration_seconds"] = -1
            (run / "metadata.json").write_text(json.dumps(metadata))
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertFalse(runs[0]["usable_failure"])
            self.assertTrue(runs[0]["review_required"])
            self.assertIn("REVIEW REQUIRED", runs[0]["state"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")

    def test_missing_completed_failure_runtime_values_require_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            run = self.make_run(
                root,
                "2026-08-15T120000Z-baseline",
                "baseline",
                xid109=True,
            )
            metadata = json.loads((run / "metadata.json").read_text())
            metadata["duration_seconds"] = None
            metadata["proton_exit_code"] = None
            (run / "metadata.json").write_text(json.dumps(metadata))
            with mock.patch.object(workflow_status, "RESULTS", root):
                runs, _, order = workflow_status.all_runs()
            self.assertFalse(runs[0]["usable_failure"])
            self.assertIn("duration or Proton exit status", runs[0]["state"])
            self.assertEqual(workflow_status.next_action(runs, order), "REVIEW")


if __name__ == "__main__":
    unittest.main()
