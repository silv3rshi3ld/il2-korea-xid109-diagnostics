from __future__ import annotations

import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone


ROOT = pathlib.Path(__file__).resolve().parents[1]


def make_executable(path: pathlib.Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ShellRobustnessTests(unittest.TestCase):
    def test_collect_system_is_private_and_propagates_probe_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            make_executable(
                fake_bin / "nvidia-smi",
                "#!/usr/bin/env bash\nprintf 'synthetic NVIDIA failure\\n'\nexit 7\n",
            )
            make_executable(
                fake_bin / "vulkaninfo",
                "#!/usr/bin/env bash\nprintf 'synthetic Vulkan summary\\n'\n",
            )
            output = root / "output"
            env = dict(os.environ)
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'umask 000; exec "$1" "$2"',
                    "collect-system-test",
                    str(ROOT / "tools/collect-system.sh"),
                    str(output),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            system_file = output / "system.txt"
            self.assertEqual(stat.S_IMODE(system_file.stat().st_mode), 0o600)
            self.assertIn("probe_failed exit_status=7", system_file.read_text())
            self.assertIn("required per-run system probe(s) failed", result.stderr)

    def test_finalizer_uses_proton_runtime_and_warns_for_empty_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = pathlib.Path(temporary) / "repo"
            shutil.copytree(ROOT / "tools", repo / "tools")
            shutil.copytree(ROOT / "analyzer", repo / "analyzer")
            run = repo / "results/2026-08-16T120000Z-baseline"
            (run / "shaders").mkdir(parents=True)
            (run / ".capture-in-progress").write_text("in progress\n")
            now = int(time.time())
            start_utc = datetime.fromtimestamp(now - 120, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            (run / "start-epoch.txt").write_text(f"{now - 120}\n")
            (run / "start-utc.txt").write_text(f"{start_utc}\n")
            (run / "proton-runtime-start-epoch.txt").write_text(f"{now}\n")
            (run / "proton-runtime-start-utc.txt").write_text(
                datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n"
            )
            observation_start = now
            (run / "observation-start-epoch.txt").write_text(f"{observation_start}\n")
            (run / "observation-start-utc.txt").write_text(
                datetime.fromtimestamp(observation_start, timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                + "\n"
            )
            (run / ".observation-start-recorded").write_text("recorded\n")
            (run / "boot-id-start.txt").write_text("unavailable\n")
            (run / "journal-cursor-start.txt").write_text("unavailable\n")
            (run / "kernel-live.log").write_text("")
            (run / "journal-follow-errors.log").write_text("")
            (run / "capture-warnings.txt").write_text("")
            (run / "proton.log").write_text("")
            (run / "vkd3d.log").write_text("")
            (run / "metadata.json").write_text(
                json.dumps({"case": "baseline", "capture_complete": False}) + "\n"
            )
            fake_bin = pathlib.Path(temporary) / "bin"
            fake_bin.mkdir()
            make_executable(fake_bin / "journalctl", "#!/usr/bin/env bash\nexit 1\n")
            env = dict(os.environ)
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            result = subprocess.run(
                [str(repo / "tools/finalize-run.sh"), "--run-dir", str(run), "--exit-code", "0"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            metadata = json.loads((run / "metadata.json").read_text())
            self.assertLess(metadata["duration_seconds"], 10)
            self.assertLess(metadata["observation_duration_seconds"], 10)
            self.assertIsNotNone(metadata["observation_start_utc"])
            self.assertIn("Proton log is empty", metadata["capture_warnings"])
            self.assertIn("VKD3D log is empty", metadata["capture_warnings"])
            self.assertNotIn(
                "Proton runtime start was missing; duration includes capture preflight",
                metadata["capture_warnings"],
            )

    def test_uncompressed_nvidia_report_blocks_duplicate_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = pathlib.Path(temporary) / "repo"
            tools = repo / "tools"
            tools.mkdir(parents=True)
            shutil.copy2(ROOT / "tools/collect-nvidia-report.sh", tools)
            report = repo / "results/nvidia-reports/nvidia-bug-report-existing.log"
            report.parent.mkdir(parents=True)
            report.write_text("private report\n")
            fake_bin = pathlib.Path(temporary) / "bin"
            fake_bin.mkdir()
            make_executable(fake_bin / "nvidia-bug-report.sh", "#!/usr/bin/env bash\nexit 0\n")
            env = dict(os.environ)
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            result = subprocess.run(
                [str(tools / "collect-nvidia-report.sh"), "--run"],
                env=env,
                input="y\n",
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("A report already exists", result.stderr)

    def test_install_checks_target_only_after_acquiring_lock(self) -> None:
        source = (ROOT / "tools/il2-diag.sh").read_text()
        install = source[source.index("cmd_install()") : source.index("cmd_uninstall()")]
        self.assertLess(install.index("flock -n 8"), install.index("[[ ! -e $tool_dir ]]") )


if __name__ == "__main__":
    unittest.main()
