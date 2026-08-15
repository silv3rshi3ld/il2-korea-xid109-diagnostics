from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_BUILD = "experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15"
EXPECTED_VKD3D = "238f157e1d64f90e0d90593557c092ab8af6e0a3"


def make_executable(path: pathlib.Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstallationIntegrationTests(unittest.TestCase):
    def test_install_select_and_recoverable_uninstall_use_only_fake_steam(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = pathlib.Path(temporary)
            repo = temp / "repo"
            shutil.copytree(
                ROOT,
                repo,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "results", "output", "build-manifest.json"),
            )
            (repo / "results").mkdir()
            (repo / "results/.gitkeep").touch()
            artifact_root = repo / "build/output/vkd3d-proton-diag"
            artifacts = []
            for relative, content in (
                ("x64/d3d12.dll", b"diag64shim"),
                ("x64/d3d12core.dll", b"diag64core"),
                ("x86/d3d12.dll", b"diag32shim"),
                ("x86/d3d12core.dll", b"diag32core"),
            ):
                path = artifact_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                artifacts.append({"path": relative, "size": len(content), "sha256": sha256(path)})
            (repo / "build-manifest.json").write_text(
                json.dumps(
                    {
                        "source": {"commit": EXPECTED_VKD3D},
                        "build": {"buildtype": "release", "enable_trace": True},
                        "artifacts": artifacts,
                    }
                )
            )

            steam = temp / "steam"
            baseline = steam / "steamapps/common/Proton - Experimental"
            core = baseline / "files/lib/wine/vkd3d-proton/x86_64-windows/d3d12core.dll"
            core.parent.mkdir(parents=True)
            core.write_bytes(b"ordinary-core")
            (baseline / "files/lib/wine/vkd3d-proton/version").write_text(f" {EXPECTED_VKD3D} vkd3d-proton\n")
            (baseline / "version").write_text(f"1723725361 {EXPECTED_BUILD}\n")
            (baseline / "compatibilitytool.vdf").write_text("ordinary manifest\n")
            (baseline / "toolmanifest.vdf").write_text("ordinary tool manifest\n")
            make_executable(
                baseline / "proton",
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' 'synthetic Proton log' >\"$PROTON_LOG_DIR/steam-$SteamAppId.log\"\n"
                "printf '%s\\n' 'Device lost observed, analyzing breadcrumbs ...' "
                "'Done analyzing breadcrumbs ...' >\"$VKD3D_LOG_FILE\"\n"
                "printf '%s' synthetic >\"$VKD3D_SHADER_DUMP_PATH/0123456789abcdef.dxil\"\n"
                "exit 0\n",
            )

            fake_bin = temp / "fake-bin"
            fake_bin.mkdir()
            make_executable(
                fake_bin / "journalctl",
                "#!/usr/bin/env bash\n"
                "case \"$*\" in\n"
                "  *--show-cursor*) printf '%s\\n' '-- cursor: s=synthetic' ;;\n"
                "  *--after-cursor*) printf '%s\\n' "
                "'2026-08-15T14:32:10+0000 host kernel: NVRM: Xid (PCI:0000:01:00): 109, name=IL2Series.exe, channel 0x00000028, errorString CTX SWITCH TIMEOUT, Info 0x1c022' ;;\n"
                "esac\n"
                "exit 0\n",
            )
            make_executable(
                fake_bin / "nvidia-smi",
                "#!/usr/bin/env bash\nprintf '%s\\n' '0, NVIDIA GeForce RTX 3090, 00000000:01:00.0, 610.57.04'\n",
            )
            make_executable(
                fake_bin / "vulkaninfo",
                "#!/usr/bin/env bash\nprintf '%s\\n' VK_NV_device_diagnostic_checkpoints VK_EXT_descriptor_buffer\n",
            )
            home = temp / "home"
            home.mkdir()
            env = dict(os.environ)
            env.update(
                {
                    "HOME": str(home),
                    "IL2_DIAG_STEAM_ROOT": str(steam),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                }
            )
            command = repo / "tools/il2-diag.sh"

            doctor = subprocess.run(
                [str(command), "doctor"], env=env, text=True, capture_output=True, check=False
            )
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            install = subprocess.run(
                [str(command), "install"], env=env, text=True, capture_output=True, check=False
            )
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
            tool = steam / "compatibilitytools.d/IL2 Xid109 Diagnostic"
            self.assertEqual(core.read_bytes(), b"ordinary-core")
            self.assertEqual(
                (tool / "files/lib/wine/vkd3d-proton/x86_64-windows/d3d12core.dll").read_bytes(),
                b"diag64core",
            )
            self.assertTrue((tool / "proton.real").is_file())
            self.assertIn("il2-xid109-diagnostic", (tool / "compatibilitytool.vdf").read_text())

            select = subprocess.run(
                [str(command), "select", "no-descriptor-buffer"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(select.returncode, 0, select.stdout + select.stderr)
            self.assertEqual(
                (tool / ".il2-xid109-diagnostic/selected-case").read_text().strip(),
                "no-descriptor-buffer",
            )

            launch_env = dict(env)
            launch_env.update({"SteamAppId": "247970", "STEAM_COMPAT_APP_ID": "247970"})
            launch = subprocess.run(
                [str(tool / "proton"), "run", "synthetic-game.exe"],
                env=launch_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(launch.returncode, 0, launch.stdout + launch.stderr)
            runs = [
                path
                for path in (repo / "results").iterdir()
                if path.is_dir() and (path / "metadata.json").is_file()
            ]
            self.assertEqual(len(runs), 1)
            run = runs[0]
            self.assertTrue((run / ".capture-complete").is_file())
            self.assertTrue((run / "proton.log").is_file())
            self.assertTrue((run / "vkd3d.log").is_file())
            self.assertTrue((run / "kernel-full.log").is_file())
            self.assertTrue((run / "kernel-window.log").is_file())
            self.assertTrue((run / "xid-events.json").is_file())
            self.assertTrue((run / "shader-manifest.json").is_file())
            self.assertTrue((run / "run-summary.txt").is_file())
            self.assertIn(
                "VKD3D_DISABLE_EXTENSIONS=VK_EXT_descriptor_buffer",
                (run / "environment.txt").read_text(),
            )
            metadata = json.loads((run / "metadata.json").read_text())
            self.assertTrue(metadata["capture_complete"])
            xid_events = json.loads((run / "xid-events.json").read_text())["events"]
            self.assertEqual(xid_events[0]["xid"], 109)

            uninstall = subprocess.run(
                [str(command), "uninstall"], env=env, text=True, capture_output=True, check=False
            )
            self.assertEqual(uninstall.returncode, 0, uninstall.stdout + uninstall.stderr)
            self.assertFalse(tool.exists())
            disabled = list((steam / "compatibilitytools.d-disabled").iterdir())
            self.assertEqual(len(disabled), 1)
            self.assertTrue((disabled[0] / ".il2-xid109-diagnostic/identity").is_file())


if __name__ == "__main__":
    unittest.main()
