from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
VERIFY = ROOT / "tools/verify-build.py"


class BuildVerifierTests(unittest.TestCase):
    def make_fixture(self, root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
        source_lock = json.loads((ROOT / "build/source-lock.json").read_text())
        artifact_root = root / "artifacts"
        artifacts = []
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
            content[68:70] = (
                0x8664 if relative.startswith("x64/") else 0x014C
            ).to_bytes(2, "little")
            path = artifact_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            artifacts.append(
                {
                    "path": relative,
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        locked_patch = source_lock["patches"][0]
        manifest = {
            "schema_version": 1,
            "build_started_utc": "2026-08-15T14:12:47Z",
            "build_finished_utc": "2026-08-15T14:13:50Z",
            "source": {
                "repository": source_lock["vkd3d_proton"]["repository"],
                "commit": source_lock["vkd3d_proton"]["commit"],
                "dirty": True,
                "status_porcelain": [" M libs/vkd3d/breadcrumbs.c"],
                "submodules": source_lock["vkd3d_proton"]["submodules"],
                "patch": {
                    "path": locked_patch["path"],
                    "sha256": locked_patch["sha256"],
                    "diff_sha256": locked_patch["diff_sha256"],
                },
            },
            "build": {
                "buildtype": "release",
                "enable_trace": True,
                "strip": True,
                "meson_arguments": source_lock["build"]["meson_arguments"],
                "source_date_epoch": source_lock["build"]["source_date_epoch"],
                "locale": "C",
                "timezone": "UTC",
            },
            "toolchain": json.loads((ROOT / "build-manifest.json").read_text())["toolchain"],
            "artifacts": artifacts,
        }
        manifest_path = root / "build-manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        return manifest_path, artifact_root

    def verify(self, manifest: pathlib.Path, artifacts: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(VERIFY), "--manifest", str(manifest), "--artifact-root", str(artifacts)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_accepts_complete_locked_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, artifacts = self.make_fixture(pathlib.Path(temporary))
            result = self.verify(manifest, artifacts)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_a_different_source_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, artifacts = self.make_fixture(pathlib.Path(temporary))
            value = json.loads(manifest.read_text())
            value["source"]["patch"]["diff_sha256"] = "a" * 64
            manifest.write_text(json.dumps(value))
            result = self.verify(manifest, artifacts)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact source diff hash", result.stdout + result.stderr)

    def test_rejects_missing_schema_required_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, artifacts = self.make_fixture(pathlib.Path(temporary))
            value = json.loads(manifest.read_text())
            value.pop("build_started_utc")
            value.pop("toolchain")
            manifest.write_text(json.dumps(value))
            result = self.verify(manifest, artifacts)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("build_started_utc", result.stdout + result.stderr)
            self.assertIn("toolchain", result.stdout + result.stderr)

    def test_rejects_incomplete_submodule_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, artifacts = self.make_fixture(pathlib.Path(temporary))
            value = json.loads(manifest.read_text())
            value["source"]["submodules"] = {}
            manifest.write_text(json.dumps(value))
            result = self.verify(manifest, artifacts)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("recursive submodule set", result.stdout + result.stderr)

    def test_rejects_incomplete_toolchain_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, artifacts = self.make_fixture(pathlib.Path(temporary))
            value = json.loads(manifest.read_text())
            value["toolchain"] = {"python": "Python test"}
            manifest.write_text(json.dumps(value))
            result = self.verify(manifest, artifacts)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("toolchain provenance", result.stdout + result.stderr)

    def test_rejects_symlinked_artifact_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, artifacts = self.make_fixture(pathlib.Path(temporary))
            real_x64 = artifacts / "x64-real"
            (artifacts / "x64").rename(real_x64)
            (artifacts / "x64").symlink_to(real_x64, target_is_directory=True)
            result = self.verify(manifest, artifacts)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe artifact path", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
