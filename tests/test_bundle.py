from __future__ import annotations

import hashlib
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TesterBundleVerificationTests(unittest.TestCase):
    def test_verifies_and_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            payload = root / "payload.txt"
            payload.write_bytes(b"prepared diagnostic payload")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            (root / "bundle-checksums.sha256").write_text(f"{digest}  payload.txt\n")
            command = [
                str(ROOT / "tools/verify-tester-bundle.py"),
                "--root",
                str(root),
            ]
            valid = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            payload.write_bytes(b"tampered")
            invalid = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("checksum mismatch", invalid.stdout + invalid.stderr)

    def test_rejects_parent_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / "bundle-checksums.sha256").write_text(f"{'0' * 64}  ../outside\n")
            result = subprocess.run(
                [str(ROOT / "tools/verify-tester-bundle.py"), "--root", str(root)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe checksum path", result.stdout + result.stderr)

    def test_rejects_a_declared_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            target = root / "target"
            target.write_text("safe")
            (root / "declared").symlink_to(target.name)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            (root / "bundle-checksums.sha256").write_text(f"{digest}  declared\n")
            result = subprocess.run(
                [str(ROOT / "tools/verify-tester-bundle.py"), "--root", str(root)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe symlink", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
