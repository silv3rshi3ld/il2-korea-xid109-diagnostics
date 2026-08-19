from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import time
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
            (repo / "results/.gitkeep").touch()
            artifact_root = repo / "build/output/vkd3d-proton-diag"
            artifacts = []
            artifact_contents = {}
            for relative in (
                "x64/d3d12.dll",
                "x64/d3d12core.dll",
                "x86/d3d12.dll",
                "x86/d3d12core.dll",
            ):
                content = bytearray(128)
                content[:2] = b"MZ"
                content[0x3C:0x40] = (64).to_bytes(4, "little")
                content[64:68] = b"PE\0\0"
                machine = 0x8664 if relative.startswith("x64/") else 0x014C
                content[68:70] = machine.to_bytes(2, "little")
                artifact_contents[relative] = bytes(content)
                path = artifact_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                artifacts.append({"path": relative, "size": len(content), "sha256": sha256(path)})
            source_lock = json.loads((repo / "build/source-lock.json").read_text())
            (repo / "build-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "build_started_utc": "2026-08-16T10:00:00Z",
                        "build_finished_utc": "2026-08-16T10:01:00Z",
                        "toolchain": json.loads(
                            (ROOT / "build-manifest.json").read_text()
                        )["toolchain"],
                        "source": {
                            "repository": "https://github.com/HansKristian-Work/vkd3d-proton.git",
                            "commit": EXPECTED_VKD3D,
                            "dirty": True,
                            "status_porcelain": [" M libs/vkd3d/breadcrumbs.c"],
                            "submodules": source_lock["vkd3d_proton"]["submodules"],
                            "patch": {
                                "path": source_lock["patches"][0]["path"],
                                "sha256": source_lock["patches"][0]["sha256"],
                                "diff_sha256": source_lock["patches"][0]["diff_sha256"],
                            },
                        },
                        "build": {
                            "buildtype": "release",
                            "enable_trace": True,
                            "enable_descriptor_qa": True,
                            "strip": True,
                            "meson_arguments": source_lock["build"]["meson_arguments"],
                            "source_date_epoch": source_lock["build"]["source_date_epoch"],
                            "locale": source_lock["build"]["locale"],
                            "timezone": source_lock["build"]["timezone"],
                        },
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
            (steam / "steamapps/appmanifest_247970.acf").write_text(
                '"AppState"\n{\n    "appid"    "247970"\n}\n'
            )
            make_executable(
                baseline / "proton",
                "#!/usr/bin/env bash\n"
                "if [[ ${1:-} == getcompatpath ]]; then exit 0; fi\n"
                "if [[ -n ${SYNTHETIC_PROTON_INVOKED:-} ]]; then printf invoked >>\"$SYNTHETIC_PROTON_INVOKED\"; fi\n"
                "printf '%s\\n' 'synthetic Proton log' >\"$PROTON_LOG_DIR/steam-$SteamAppId.log\"\n"
                "printf '%s\\n' 'Device lost observed, analyzing breadcrumbs ...' "
                "'Reporting NVIDIA checkpoints for direct queue 0.' "
                "'Found pending command list context 1 in executable state, TOP_OF_PIPE marker 2, BOTTOM_OF_PIPE marker 1.' "
                "'===== Potential crash region BEGIN =====' 'Command: dispatch' "
                "'===== Potential crash region END =====' "
                "'Done analyzing breadcrumbs ...' >\"$VKD3D_LOG_FILE\"\n"
                "printf '%s' synthetic >\"$VKD3D_SHADER_DUMP_PATH/0123456789abcdef.dxil\"\n"
                "if [[ -n ${VKD3D_DESCRIPTOR_QA_LOG:-} ]]; then "
                "printf '%s\\n' 'REGISTER HEAP 1 || COUNT = 1' >\"$VKD3D_DESCRIPTOR_QA_LOG\"; fi\n"
                "if [[ ${SYNTHETIC_BLOCK:-0} == 1 ]]; then "
                "trap 'exit 143' TERM INT HUP; while :; do sleep 1; done; fi\n"
                "exit 0\n",
            )

            fake_bin = temp / "fake-bin"
            fake_bin.mkdir()
            make_executable(
                fake_bin / "journalctl",
                "#!/usr/bin/env bash\n"
                "if [[ -n ${SYNTHETIC_JOURNAL_ARGS:-} ]]; then printf '%s\\n' \"$*\" >>\"$SYNTHETIC_JOURNAL_ARGS\"; fi\n"
                "case \"$*\" in\n"
                "  *--help*) printf '%s\\n' '--no-hostname --boot --after-cursor' ;;\n"
                "  *--show-cursor*) printf '%s\\n' '-- cursor: s=synthetic' ;;\n"
                "  *--follow*) if [[ ${SYNTHETIC_JOURNAL_FAIL:-0} == 1 ]]; then "
                "printf '%s\\n' 'synthetic follower failure' >&2; exit 7; fi; "
                "printf '%s\\n' '2026-08-15T14:32:10+0000 kernel: live journal capture started'; "
                "trap 'exit 0' TERM INT HUP; while :; do sleep 1; done ;;\n"
                "  *--after-cursor*) printf '%s\\n' "
                "'2026-08-15T14:32:10+0000 kernel: NVRM: Xid (PCI:0000:01:00): 109, name=IL2Series.exe, channel 0x00000028, errorString CTX SWITCH TIMEOUT, Info 0x1c022' ;;\n"
                "  *'-n 1'*) printf '%s\\n' 'Linux kernel probe' ;;\n"
                "esac\n"
                "exit 0\n",
            )
            make_executable(
                fake_bin / "nvidia-smi",
                "#!/usr/bin/env bash\nprintf '%s\\n' '0, NVIDIA GeForce RTX 3090, 00000000:01:00.0, 610.57.04'\n",
            )
            make_executable(
                fake_bin / "vulkaninfo",
                "#!/usr/bin/env bash\nprintf '%s\\n' VK_NV_device_diagnostic_checkpoints VK_EXT_descriptor_buffer VK_EXT_descriptor_heap\n",
            )
            make_executable(fake_bin / "pgrep", "#!/usr/bin/env bash\nexit 1\n")
            make_executable(
                fake_bin / "gio",
                "#!/usr/bin/env bash\n"
                "source_path=${@: -1}\n"
                "mkdir -p -- \"$SYNTHETIC_TRASH_ROOT\"\n"
                "mv -- \"$source_path\" \"$SYNTHETIC_TRASH_ROOT/\"\n",
            )
            home = temp / "home"
            home.mkdir()
            synthetic_trash = temp / "desktop-trash"
            env = dict(os.environ)
            env.update(
                {
                    "HOME": str(home),
                    "IL2_DIAG_STEAM_ROOT": str(steam),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "SYNTHETIC_TRASH_ROOT": str(synthetic_trash),
                    "XDG_SESSION_TYPE": "x11",
                }
            )
            command = repo / "tools/il2-diag.sh"

            accepted = subprocess.run(
                [str(command), "accept-terms"],
                env=env,
                input="I AGREE\n",
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

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
                artifact_contents["x64/d3d12core.dll"],
            )
            self.assertTrue((tool / "proton.real").is_file())
            self.assertIn("il2-xid109-diagnostic", (tool / "compatibilitytool.vdf").read_text())
            install_manifest = json.loads(
                (tool / ".il2-xid109-diagnostic/install-manifest.json").read_text()
            )
            self.assertEqual(install_manifest["tester_notice"]["terms_version"], "2026-08-19.1")

            wayland_env = dict(env)
            wayland_env["XDG_SESSION_TYPE"] = "wayland"
            wayland_select = subprocess.run(
                [str(command), "select", "no-descriptor-buffer"],
                env=wayland_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(wayland_select.returncode, 0)
            self.assertIn("requires X11", wayland_select.stderr)

            select = subprocess.run(
                [str(command), "select", "descriptor-qa"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(select.returncode, 0, select.stdout + select.stderr)
            self.assertEqual(
                (tool / ".il2-xid109-diagnostic/selected-case").read_text().strip(),
                "descriptor-qa",
            )

            helper_env = dict(env)
            helper_env.update({"SteamAppId": "247970", "STEAM_COMPAT_APP_ID": "247970"})
            helper = subprocess.run(
                [str(tool / "proton"), "getcompatpath", "247970"],
                env=helper_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(helper.returncode, 0, helper.stdout + helper.stderr)
            self.assertEqual(
                [path for path in (repo / "results").iterdir() if path.is_dir()],
                [],
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
            self.assertTrue((run / "descriptor-qa.log").is_file())
            self.assertTrue((run / "run-summary.txt").is_file())
            self.assertTrue((run / "install-manifest.json").is_file())
            self.assertTrue((run / "proton-runtime-start-utc.txt").is_file())
            self.assertTrue((run / "proton-runtime-start-epoch.txt").is_file())
            self.assertGreaterEqual(
                int((run / "proton-runtime-start-epoch.txt").read_text()),
                int((run / "start-epoch.txt").read_text()),
            )
            self.assertIn(
                f"VKD3D_DESCRIPTOR_QA_LOG={run}/descriptor-qa.log",
                (run / "environment.txt").read_text(),
            )
            metadata = json.loads((run / "metadata.json").read_text())
            self.assertTrue(metadata["capture_complete"])
            self.assertEqual(
                metadata["diagnostic_environment"]["VKD3D_DESCRIPTOR_QA_LOG"],
                "descriptor-qa.log",
            )
            xid_events = json.loads((run / "xid-events.json").read_text())["events"]
            self.assertEqual(xid_events[0]["xid"], 109)

            unauthorized = subprocess.run(
                [str(tool / "proton"), "run", "synthetic-game.exe"],
                env=launch_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(unauthorized.returncode, 0)
            self.assertIn("not authorized by the Next step", unauthorized.stderr)
            self.assertEqual(
                len(
                    [
                        path
                        for path in (repo / "results").iterdir()
                        if path.is_dir() and (path / "metadata.json").is_file()
                    ]
                ),
                1,
            )
            status_after_block = subprocess.run(
                [str(command), "status"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertIn("Last blocked launch", status_after_block.stdout)

            before_signal = set(runs)
            reselect = subprocess.run(
                [str(command), "select", "no-descriptor-buffer"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(reselect.returncode, 0, reselect.stdout + reselect.stderr)
            blocking_env = dict(launch_env)
            blocking_env["SYNTHETIC_BLOCK"] = "1"
            blocking = subprocess.Popen(
                [str(tool / "proton"), "run", "synthetic-game.exe"],
                env=blocking_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            signal_run = None
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                candidates = [
                    path
                    for path in (repo / "results").iterdir()
                    if path.is_dir()
                    and path not in before_signal
                    and (path / "proton-child.pid").is_file()
                ]
                if candidates:
                    signal_run = candidates[0]
                    break
                time.sleep(0.05)
            self.assertIsNotNone(signal_run)
            assert signal_run is not None
            child_pid = int((signal_run / "proton-child.pid").read_text())
            follower_pid = int((signal_run / "journal-follower.pid").read_text())
            ready = subprocess.run(
                [str(command), "ready"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertIn("10-minute hangar observation started", ready.stdout)
            ready_again = subprocess.run(
                [str(command), "ready"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(ready_again.returncode, 0, ready_again.stdout + ready_again.stderr)
            self.assertIn("timer was not restarted", ready_again.stdout)
            blocking.terminate()
            stdout, stderr = blocking.communicate(timeout=5)
            self.assertIn(blocking.returncode, (143, -15), stdout + stderr)
            self.assertTrue((signal_run / ".capture-complete").is_file())
            signal_metadata = json.loads((signal_run / "metadata.json").read_text())
            self.assertTrue(signal_metadata["capture_interrupted"])
            self.assertIsNotNone(signal_metadata["observation_start_utc"])
            self.assertIsNotNone(signal_metadata["observation_duration_seconds"])
            self.assertFalse(pathlib.Path(f"/proc/{child_pid}").exists())
            self.assertFalse(pathlib.Path(f"/proc/{follower_pid}").exists())

            before_kill = {
                path for path in (repo / "results").iterdir() if path.is_dir()
            }
            reselect = subprocess.run(
                [str(command), "select", "no-descriptor-buffer"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(reselect.returncode, 0, reselect.stdout + reselect.stderr)
            killed = subprocess.Popen(
                [str(tool / "proton"), "run", "synthetic-game.exe"],
                env=blocking_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            killed_run = None
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                candidates = [
                    path
                    for path in (repo / "results").iterdir()
                    if path.is_dir()
                    and path not in before_kill
                    and (path / "proton-child.pid").is_file()
                ]
                if candidates:
                    killed_run = candidates[0]
                    break
                time.sleep(0.05)
            self.assertIsNotNone(killed_run)
            assert killed_run is not None
            killed_child = int((killed_run / "proton-child.pid").read_text())
            killed_follower = int((killed_run / "journal-follower.pid").read_text())
            killed.kill()
            killed.communicate(timeout=5)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and (
                pathlib.Path(f"/proc/{killed_child}").exists()
                or pathlib.Path(f"/proc/{killed_follower}").exists()
            ):
                time.sleep(0.05)
            self.assertFalse(pathlib.Path(f"/proc/{killed_child}").exists())
            self.assertFalse(pathlib.Path(f"/proc/{killed_follower}").exists())
            killed_recovery = subprocess.run(
                [str(command), "recover"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                killed_recovery.returncode,
                0,
                killed_recovery.stdout + killed_recovery.stderr,
            )
            self.assertTrue((killed_run / ".capture-complete").is_file())

            invoked = temp / "proton-invoked.txt"
            failed_follower_env = dict(launch_env)
            failed_follower_env.update(
                {
                    "SYNTHETIC_JOURNAL_FAIL": "1",
                    "SYNTHETIC_PROTON_INVOKED": str(invoked),
                }
            )
            reselect = subprocess.run(
                [str(command), "select", "no-descriptor-buffer"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(reselect.returncode, 0, reselect.stdout + reselect.stderr)
            follower_failure = subprocess.run(
                [str(tool / "proton"), "run", "synthetic-game.exe"],
                env=failed_follower_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
            self.assertNotEqual(follower_failure.returncode, 0)
            self.assertFalse(invoked.exists())
            self.assertIn(
                "live kernel journal capture could not stay active",
                follower_failure.stderr,
            )

            interrupted = repo / "results/2026-08-15T150000Z-baseline"
            (interrupted / "shaders").mkdir(parents=True)
            (interrupted / ".capture-in-progress").write_text("interrupted\n")
            (interrupted / "start-utc.txt").write_text("2026-08-15T14:59:00Z\n")
            (interrupted / "start-epoch.txt").write_text("1786805940\n")
            (interrupted / "journal-cursor-start.txt").write_text("s=synthetic\n")
            (interrupted / "boot-id-start.txt").write_text(
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n"
            )
            (interrupted / "capture-warnings.txt").write_text("")
            (interrupted / "metadata.json").write_text(
                json.dumps(
                    {
                        "case": "baseline",
                        "start_utc": "2026-08-15T14:59:00Z",
                        "capture_complete": False,
                    }
                )
            )
            (interrupted / "vkd3d.log").write_text("Device lost observed\n")
            (interrupted / "proton.log").write_text("VK_ERROR_DEVICE_LOST\n")
            journal_args = temp / "journal-args.txt"
            recover_env = dict(env)
            recover_env["SYNTHETIC_JOURNAL_ARGS"] = str(journal_args)
            recover = subprocess.run(
                [str(command), "recover"],
                env=recover_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(recover.returncode, 0, recover.stdout + recover.stderr)
            recovered_metadata = json.loads((interrupted / "metadata.json").read_text())
            self.assertTrue(recovered_metadata["capture_complete"])
            self.assertTrue(recovered_metadata["capture_interrupted"])
            self.assertTrue(recovered_metadata["recovered_after_interruption"])
            self.assertTrue((interrupted / ".capture-complete").is_file())
            self.assertIn("--boot=aaaaaaaabbbbccccddddeeeeeeeeeeee", journal_args.read_text())

            uninstall = subprocess.run(
                [str(command), "uninstall"], env=env, text=True, capture_output=True, check=False
            )
            self.assertEqual(uninstall.returncode, 0, uninstall.stdout + uninstall.stderr)
            self.assertFalse(tool.exists())
            disabled = list((steam / "compatibilitytools.d-disabled").iterdir())
            self.assertEqual(len(disabled), 1)
            self.assertTrue((disabled[0] / ".il2-xid109-diagnostic/identity").is_file())
            removed = subprocess.run(
                [str(command), "trash-copy"],
                env=env,
                input="MOVE DISABLED COPY TO TRASH\n",
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
            self.assertEqual(list((steam / "compatibilitytools.d-disabled").iterdir()), [])
            self.assertEqual(len(list(synthetic_trash.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
