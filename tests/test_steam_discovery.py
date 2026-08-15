from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_BUILD = "experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15"
EXPECTED_VKD3D = "238f157e1d64f90e0d90593557c092ab8af6e0a3"


class SteamDiscoveryTests(unittest.TestCase):
    def test_finds_exact_proton_in_secondary_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            steam = root / "Steam"
            secondary = root / "Games Library"
            (steam / "steamapps").mkdir(parents=True)
            (steam / "steamapps/libraryfolders.vdf").write_text(
                '"libraryfolders"\n{\n  "1"\n  {\n'
                f'    "path"    "{secondary}"\n'
                "  }\n}\n"
            )
            baseline = secondary / "steamapps/common/Proton - Experimental"
            version = baseline / "files/lib/wine/vkd3d-proton/version"
            version.parent.mkdir(parents=True)
            version.write_text(f" {EXPECTED_VKD3D} vkd3d-proton\n")
            (baseline / "version").write_text(f"0 {EXPECTED_BUILD}\n")
            proton = baseline / "proton"
            proton.write_text("#!/usr/bin/env bash\nexit 0\n")
            proton.chmod(proton.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ)
            env["IL2_DIAG_STEAM_ROOT"] = str(steam)
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"source {ROOT / 'tools/lib/common.sh'}; il2_diag_baseline_dir",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(pathlib.Path(result.stdout.strip()), baseline)


if __name__ == "__main__":
    unittest.main()
