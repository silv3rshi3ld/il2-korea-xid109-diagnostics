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
                    "proton_exit_code": 0,
                    "capture_complete": complete,
                    "capture_warnings": [],
                    "capture_interrupted": False,
                }
            )
        )
        (run / "xid-events.json").write_text(
            json.dumps(
                {"events": [{"xid": 109, "name": "IL2Series.exe"}] if xid109 else []}
            )
        )
        (run / "vkd3d.log").write_text(
            "Device lost observed, analyzing breadcrumbs ...\n"
            "Reporting NVIDIA checkpoints for direct queue 0.\n"
            "Found pending command list context 1 in executable state, "
            "TOP_OF_PIPE marker 2, BOTTOM_OF_PIPE marker 1.\n"
            "===== Potential crash region BEGIN =====\n"
            "Command: dispatch\n"
            "===== Potential crash region END =====\n"
            if xid109
            else ""
        )
        (run / (".capture-complete" if complete else ".capture-in-progress")).touch()
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


if __name__ == "__main__":
    unittest.main()
