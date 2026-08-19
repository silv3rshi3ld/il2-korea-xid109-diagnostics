from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest
import json

from analyzer.parsers import parse_kernel_log


ROOT = pathlib.Path(__file__).resolve().parents[1]


class NoviceCliTests(unittest.TestCase):
    def copy_repo(self, temporary: str) -> pathlib.Path:
        repo = pathlib.Path(temporary) / "repo"
        shutil.copytree(
            ROOT,
            repo,
            ignore=shutil.ignore_patterns(
                ".git",
                "__pycache__",
                "results",
                "output",
                "build-manifest.json",
                "bundle-checksums.sha256",
                "bundle-info.json",
                "corresponding-source",
            ),
        )
        (repo / "results").mkdir()
        return repo

    def test_finish_refuses_an_incomplete_matrix_before_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.copy_repo(temporary)
            result = subprocess.run(
                [str(repo / "il2-diagnostic.sh"), "finish"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not ready", result.stderr)
            self.assertFalse(any(repo.glob("PRIVATE-il2-xid109-results-*")))

    def test_finish_rejects_an_unrecognized_candidate_before_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.copy_repo(temporary)
            candidate = repo / "results/culprit-candidate"
            candidate.mkdir()
            (candidate / "private-note.txt").write_text("not analyzer output\n")
            result = subprocess.run(
                [str(repo / "tools/pack-results.sh")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unrecognized culprit-candidate", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_finish_packs_one_complete_private_matrix_and_excludes_nvidia_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.copy_repo(temporary)
            (repo / "build-manifest.json").write_text("{}\n")
            fixture_root = repo / "tests/fixtures"
            kernel = (fixture_root / "kernel-xid109.log").read_text()
            vkd3d = (fixture_root / "vkd3d-breadcrumb.log").read_text()
            proton = (fixture_root / "proton-device-lost.log").read_text()
            cases = [
                "baseline",
                "descriptor-qa",
                "descriptor-heap",
                "single-queue",
                "no-descriptor-buffer",
                "sync",
            ]
            for index, case in enumerate(cases):
                run = repo / "results" / f"2026-08-15T120{index}00Z-{case}"
                run.mkdir()
                (run / ".capture-complete").touch()
                (run / "metadata.json").write_text(
                    json.dumps(
                        {
                            "case": case,
                            "capture_complete": True,
                            "kernel_capture_complete": True,
                            "capture_warnings": [],
                            "capture_interrupted": False,
                            "duration_seconds": 90,
                            "observation_start_utc": "2026-08-15T12:00:10Z",
                            "observation_duration_seconds": 90,
                            "proton_exit_code": 0,
                        }
                    )
                )
                (run / ".observation-start-recorded").touch()
                (run / "kernel-full.log").write_text(kernel)
                (run / "vkd3d.log").write_text(vkd3d)
                (run / "proton.log").write_text(proton)
                (run / "xid-events.json").write_text(
                    json.dumps({"events": parse_kernel_log(kernel)})
                )
                (run / "shader-manifest.json").write_text('{"shaders": []}\n')
                if case == "descriptor-qa":
                    (run / "descriptor-qa.log").write_text(
                        "REGISTER HEAP 1 || COUNT = 1\n"
                    )
                if index == 0:
                    (run / "observation-start-utc.txt.tmp.123").write_text(
                        "unfinished READY write\n"
                    )
            private_report = repo / "results/nvidia-reports/private.log.gz"
            private_report.parent.mkdir()
            private_report.write_bytes(b"must stay separate")
            stale_candidate = repo / "results/culprit-candidate.previous-2026-08-15T000000Z"
            stale_candidate.mkdir()
            (stale_candidate / "must-not-ship.txt").write_text("stale generated evidence\n")

            result = subprocess.run(
                [str(repo / "il2-diagnostic.sh"), "finish"],
                input="CREATE PRIVATE ARCHIVE\n",
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            archives = [
                path
                for path in repo.glob("PRIVATE-il2-xid109-results-*.tar.*")
                if not path.name.endswith(".sha256")
            ]
            self.assertEqual(len(archives), 1)
            self.assertTrue(pathlib.Path(str(archives[0]) + ".sha256").is_file())
            listing = subprocess.check_output(["tar", "-tf", str(archives[0])], text=True)
            self.assertNotIn("nvidia-reports", listing)
            self.assertNotIn("culprit-candidate.previous", listing)
            self.assertNotIn("tmp.123", listing)
            self.assertIn("results/analysis-summary.json", listing)
            self.assertIn("results/culprit-candidate/README.md", listing)
            self.assertTrue(stale_candidate.is_dir())
            checksum = pathlib.Path(str(archives[0]) + ".sha256")
            self.assertNotIn(str(repo), checksum.read_text())
            received = pathlib.Path(temporary) / "received"
            received.mkdir()
            received_archive = received / archives[0].name
            received_checksum = received / checksum.name
            shutil.move(archives[0], received_archive)
            shutil.move(checksum, received_checksum)
            verified = subprocess.run(
                ["sha256sum", "-c", received_checksum.name],
                cwd=received,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)


if __name__ == "__main__":
    unittest.main()
